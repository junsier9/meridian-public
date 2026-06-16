from __future__ import annotations

import argparse
import json
import os
import time
from argparse import Namespace
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.testnet_flatten_runner import (
    TESTNET_FLATTEN_CONFIRMATION,
    run_testnet_reduce_only_flatten,
)
from enhengclaw.live_trading.testnet_strategy_runner import (
    TESTNET_STRATEGY_CONFIRMATION,
    run_testnet_strategy_auto_order,
)
from enhengclaw.quant_research.contracts import write_json


TESTNET_RECURRING_CONFIRMATION = (
    "I_UNDERSTAND_THIS_SUBMITS_RECURRING_BINANCE_USDM_TESTNET_STRATEGY_ORDERS_AND_FLATTENS_EACH_CYCLE"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Testnet-only recurring strategy order loop with forced reduce-only flatten after each cycle."
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=2)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--execute-testnet-recurring-loop", action="store_true")
    parser.add_argument("--i-understand-this-uses-binance-usdm-testnet", action="store_true")
    parser.add_argument("--confirm-testnet-recurring-risk", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_testnet_recurring_auto_order_loop(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_testnet_recurring_auto_order_loop(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    strategy_runner: Callable[..., tuple[dict[str, Any], int]] = run_testnet_strategy_auto_order,
    flatten_runner: Callable[..., tuple[dict[str, Any], int]] = run_testnet_reduce_only_flatten,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(
        getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_testnet_sizing.yaml")
    )
    max_cycles = int(getattr(args, "max_cycles", 0) or 0)
    interval_seconds = max(0.0, float(getattr(args, "interval_seconds", 0.0) or 0.0))
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-testnet-recurring-loop"
    loop_root = live_config.artifact_root.parent / "testnet_recurring_loop" / run_id
    loop_root.mkdir(parents=True, exist_ok=True)
    blockers = _confirmation_blockers(args)
    if max_cycles <= 0:
        blockers.append("max_cycles_must_be_positive")
    if max_cycles > 3:
        blockers.append(f"max_cycles_exceeds_gate_cap:actual={max_cycles}:cap=3")
    if str(dict(live_config.payload.get("binance") or {}).get("venue") or "").strip().lower() != "usdm_futures_testnet":
        blockers.append("recurring_loop_requires_usdm_futures_testnet_venue")
    if blockers:
        summary = _summary(
            run_id=run_id,
            status="testnet_recurring_loop_blocked",
            blockers=blockers,
            started=started,
            loop_root=loop_root,
            max_cycles=max_cycles,
            interval_seconds=interval_seconds,
            cycles=[],
        )
        _write_summary(loop_root, summary)
        return summary, 2

    cycle_rows: list[dict[str, Any]] = []
    env_mapping = env or os.environ
    for cycle_index in range(1, max_cycles + 1):
        cycle_started = datetime.now(UTC)
        cycle = _run_cycle(
            args=args,
            cycle_index=cycle_index,
            env=env_mapping,
            strategy_runner=strategy_runner,
            flatten_runner=flatten_runner,
        )
        cycle["cycle_index"] = int(cycle_index)
        cycle["started_at_utc"] = cycle_started.isoformat().replace("+00:00", "Z")
        cycle["finished_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        cycle_rows.append(cycle)
        write_json(loop_root / f"cycle_{cycle_index:03d}.json", cycle)
        if cycle["blockers"]:
            break
        if cycle_index < max_cycles and interval_seconds > 0.0:
            time.sleep(interval_seconds)

    loop_blockers = sorted({item for row in cycle_rows for item in list(row.get("blockers") or [])})
    summary = _summary(
        run_id=run_id,
        status="testnet_recurring_loop_completed"
        if not loop_blockers and len(cycle_rows) == max_cycles
        else "testnet_recurring_loop_blocked",
        blockers=loop_blockers,
        started=started,
        loop_root=loop_root,
        max_cycles=max_cycles,
        interval_seconds=interval_seconds,
        cycles=cycle_rows,
    )
    _write_summary(loop_root, summary)
    return summary, 0 if summary["status"] == "testnet_recurring_loop_completed" else 2


def _run_cycle(
    *,
    args: argparse.Namespace,
    cycle_index: int,
    env: Mapping[str, str],
    strategy_runner: Callable[..., tuple[dict[str, Any], int]],
    flatten_runner: Callable[..., tuple[dict[str, Any], int]],
) -> dict[str, Any]:
    strategy_summary, strategy_exit_code = strategy_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            as_of=str(getattr(args, "as_of", "now") or "now"),
            fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
            symbols=str(getattr(args, "symbols", "") or ""),
            public_market_data=bool(getattr(args, "public_market_data", False)),
            execute_testnet_strategy_orders=True,
            i_understand_this_uses_binance_usdm_testnet=True,
            confirm_testnet_risk=TESTNET_STRATEGY_CONFIRMATION,
        ),
        env=env,
    )
    flatten_summary, flatten_exit_code = flatten_runner(
        Namespace(
            config=str(getattr(args, "config", "")),
            execute_testnet_flatten=True,
            i_understand_this_uses_binance_usdm_testnet=True,
            confirm_testnet_flatten=TESTNET_FLATTEN_CONFIRMATION,
        ),
        env=env,
    )
    blockers = _cycle_blockers(
        cycle_index=cycle_index,
        strategy_summary=strategy_summary,
        strategy_exit_code=int(strategy_exit_code),
        flatten_summary=flatten_summary,
        flatten_exit_code=int(flatten_exit_code),
    )
    return {
        "cycle_index": int(cycle_index),
        "blockers": blockers,
        "strategy_status": str(strategy_summary.get("status") or ""),
        "strategy_exit_code": int(strategy_exit_code),
        "strategy_artifact_root": str(strategy_summary.get("artifact_root") or ""),
        "strategy_blockers": list(strategy_summary.get("blockers") or []),
        "strategy_submitted_order_count": int(strategy_summary.get("submitted_order_count") or 0),
        "strategy_fill_count": int(strategy_summary.get("fill_count") or 0),
        "flatten_status": str(flatten_summary.get("status") or ""),
        "flatten_exit_code": int(flatten_exit_code),
        "flatten_artifact_root": str(flatten_summary.get("artifact_root") or ""),
        "flatten_blockers": list(flatten_summary.get("blockers") or []),
        "flatten_planned_order_count": int(flatten_summary.get("planned_order_count") or 0),
        "flatten_submitted_order_count": int(flatten_summary.get("submitted_order_count") or 0),
        "flatten_fill_count": int(flatten_summary.get("fill_count") or 0),
        "flatten_open_order_count_before": int(flatten_summary.get("open_order_count_before") or 0),
        "flatten_open_position_count_before": int(flatten_summary.get("open_position_count_before") or 0),
        "flatten_open_order_count_after": _coalesce_count(
            flatten_summary.get("open_order_count_after"), flatten_summary.get("open_order_count_before")
        ),
        "flatten_open_position_count_after": _coalesce_count(
            flatten_summary.get("open_position_count_after"), flatten_summary.get("open_position_count_before")
        ),
    }


def _cycle_blockers(
    *,
    cycle_index: int,
    strategy_summary: dict[str, Any],
    strategy_exit_code: int,
    flatten_summary: dict[str, Any],
    flatten_exit_code: int,
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(str(item) for item in list(strategy_summary.get("blockers") or []))
    blockers.extend(str(item) for item in list(flatten_summary.get("blockers") or []))
    strategy_submitted = int(strategy_summary.get("submitted_order_count") or 0)
    strategy_fills = int(strategy_summary.get("fill_count") or 0)
    flatten_planned = int(flatten_summary.get("planned_order_count") or 0)
    flatten_submitted = int(flatten_summary.get("submitted_order_count") or 0)
    flatten_fills = int(flatten_summary.get("fill_count") or 0)
    flatten_after_orders = _coalesce_count(flatten_summary.get("open_order_count_after"), flatten_summary.get("open_order_count_before"))
    flatten_after_positions = _coalesce_count(
        flatten_summary.get("open_position_count_after"), flatten_summary.get("open_position_count_before")
    )
    if strategy_exit_code != 0 or strategy_summary.get("status") != "testnet_strategy_orders_submitted":
        blockers.append(f"recurring_strategy_cycle_failed:{cycle_index}:{strategy_summary.get('status')}")
    if strategy_submitted <= 0:
        blockers.append(f"recurring_strategy_no_submitted_orders:{cycle_index}")
    if strategy_submitted != strategy_fills:
        blockers.append(f"recurring_strategy_submit_fill_mismatch:{cycle_index}:{strategy_submitted}:{strategy_fills}")
    if flatten_exit_code != 0:
        blockers.append(f"recurring_flatten_cycle_failed:{cycle_index}:{flatten_summary.get('status')}")
    if strategy_submitted > 0 and flatten_summary.get("status") != "testnet_reduce_only_flatten_executed":
        blockers.append(f"recurring_flatten_cycle_failed:{cycle_index}:{flatten_summary.get('status')}")
    if strategy_submitted > 0 and flatten_planned <= 0:
        blockers.append(f"recurring_flatten_no_planned_orders:{cycle_index}")
    if flatten_submitted != flatten_fills:
        blockers.append(f"recurring_flatten_submit_fill_mismatch:{cycle_index}:{flatten_submitted}:{flatten_fills}")
    if strategy_submitted != flatten_submitted:
        blockers.append(f"recurring_strategy_flatten_count_mismatch:{cycle_index}:{strategy_submitted}:{flatten_submitted}")
    if flatten_after_orders != 0:
        blockers.append(f"recurring_residual_open_orders:{cycle_index}:{flatten_after_orders}")
    if flatten_after_positions != 0:
        blockers.append(f"recurring_residual_open_positions:{cycle_index}:{flatten_after_positions}")
    return sorted(set(blockers))


def _confirmation_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "execute_testnet_recurring_loop", False)):
        blockers.append("missing_execute_testnet_recurring_loop_flag")
    if not bool(getattr(args, "i_understand_this_uses_binance_usdm_testnet", False)):
        blockers.append("missing_testnet_understanding_flag")
    if str(getattr(args, "confirm_testnet_recurring_risk", "") or "").strip() != TESTNET_RECURRING_CONFIRMATION:
        blockers.append("missing_exact_testnet_recurring_confirmation")
    return blockers


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started: datetime,
    loop_root: Any,
    max_cycles: int,
    interval_seconds: float,
    cycles: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": "testnet_recurring_loop",
        "status": status,
        "blockers": sorted(set(blockers)),
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(loop_root),
        "max_cycles": int(max_cycles),
        "completed_cycle_count": int(len(cycles)),
        "interval_seconds": float(interval_seconds),
        "testnet_only": True,
        "exchange_order_submission": "enabled_testnet_only",
        "mainnet_order_submission": "disabled",
        "forced_flatten_each_cycle": True,
        "strategy_submitted_order_count_total": int(
            sum(int(row.get("strategy_submitted_order_count") or 0) for row in cycles)
        ),
        "strategy_fill_count_total": int(sum(int(row.get("strategy_fill_count") or 0) for row in cycles)),
        "flatten_submitted_order_count_total": int(
            sum(int(row.get("flatten_submitted_order_count") or 0) for row in cycles)
        ),
        "flatten_fill_count_total": int(sum(int(row.get("flatten_fill_count") or 0) for row in cycles)),
        "final_open_order_count": None if not cycles else int(cycles[-1].get("flatten_open_order_count_after") or 0),
        "final_open_position_count": None if not cycles else int(cycles[-1].get("flatten_open_position_count_after") or 0),
        "cycles": cycles,
    }


def _write_summary(loop_root: Any, summary: dict[str, Any]) -> None:
    write_json(loop_root / "testnet_recurring_loop_summary.json", summary)
    write_json(loop_root / "run_summary.json", summary)


def _coalesce_count(primary: Any, fallback: Any) -> int:
    if primary is None:
        return int(fallback or 0)
    return int(primary or 0)


if __name__ == "__main__":
    raise SystemExit(main())
