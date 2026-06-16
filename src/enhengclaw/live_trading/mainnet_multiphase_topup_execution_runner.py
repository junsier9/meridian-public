from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.frozen_frontier_live import FRONTIER_PLAN_ARTIFACT
from enhengclaw.live_trading.live_pit_universe import LIVE_UNIVERSE_ARTIFACT
from enhengclaw.live_trading.mainnet_delta_execution_runner import (
    _load_source_plan,
    _required_confirmation,
    run_mainnet_delta_execution,
)
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import MULTIPHASE_TARGET_ENGINE
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json


CONFIRMATION_PREFIX = "LIVE_MULTIPHASE_TOPUP:HV_BALANCED:MAINNET"
DEFAULT_ALLOWED_DELTA_CLASSIFICATIONS = {"increase_same_side"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and optionally execute an explicit mainnet multiphase capital top-up plan. "
            "Default mode is signed/read-only delta preflight; live orders require an exact top-up confirmation."
        )
    )
    parser.add_argument(
        "--config",
        default="config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve150_topup_live_execution_candidate.yaml",
    )
    parser.add_argument("--plan-artifact", required=True)
    parser.add_argument("--expected-reserve-usdt", type=float, default=150.0)
    parser.add_argument("--allowed-delta-classifications", default="increase_same_side")
    parser.add_argument("--execute-mainnet-topup-orders", action="store_true")
    parser.add_argument("--operator-enable-mainnet-topup-for-this-run", action="store_true")
    parser.add_argument("--i-understand-this-places-real-mainnet-topup-orders", action="store_true")
    parser.add_argument("--i-understand-daily-realized-pnl-gate-is-active", action="store_true")
    parser.add_argument("--confirm-mainnet-topup-execution", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--ignore-heartbeat-run-id", default="")
    args = parser.parse_args(argv)
    summary, exit_code = run_mainnet_multiphase_topup_execution(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_mainnet_multiphase_topup_execution(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    delta_runner: Callable[..., tuple[dict[str, Any], int]] = run_mainnet_delta_execution,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(str(getattr(args, "config", "")))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-multiphase-topup-execution"
    run_root = live_config.artifact_root.parent / "mainnet_multiphase_topup_execution" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    state_store = LiveTradingStateStore(live_config.sqlite_path)
    state_store.initialize()

    source_plan = _load_source_plan(str(getattr(args, "plan_artifact", "") or ""))
    topup_plan_hash = _topup_plan_artifact_hash(Path(str(source_plan.get("plan_root") or "")))
    required_topup_confirmation = _required_topup_confirmation(
        plan_hash=str(topup_plan_hash or "missing"),
        reserve_usdt=float(getattr(args, "expected_reserve_usdt", 150.0) or 150.0),
    )
    required_delta_confirmation = _required_confirmation(
        plan_hash=str(source_plan.get("plan_hash") or "missing"),
        execution_stage="entry_second",
    )

    topup_preflight = _topup_source_preflight(
        source_plan=source_plan,
        payload=payload,
        expected_reserve_usdt=float(getattr(args, "expected_reserve_usdt", 150.0) or 150.0),
        allowed_delta_classifications=_csv_set(
            getattr(args, "allowed_delta_classifications", "increase_same_side")
        ),
    )
    blockers = [str(item) for item in list(source_plan.get("blockers") or [])]
    blockers.extend(str(item) for item in list(topup_preflight.get("blockers") or []))
    execute = bool(getattr(args, "execute_mainnet_topup_orders", False))
    if execute:
        blockers.extend(
            _execute_confirmation_blockers(
                args,
                payload=payload,
                required_confirmation=required_topup_confirmation,
            )
        )

    write_json(run_root / "topup_source_preflight.json", topup_preflight)
    delta_summary: dict[str, Any] = {"status": "not_run", "blockers": []}
    delta_exit_code = 0
    if not blockers:
        delta_args = _delta_args(
            args,
            execute=execute,
            delta_confirmation=required_delta_confirmation,
        )
        delta_summary, delta_exit_code = delta_runner(delta_args, env=env or os.environ, now_fn=now_fn)
        write_json(run_root / "delta_runner_summary.json", delta_summary)
        if delta_exit_code != 0:
            blockers.append(f"delta_runner_exit_code:{delta_exit_code}")
        blockers.extend(str(item) for item in list(delta_summary.get("blockers") or []))
    else:
        write_json(run_root / "delta_runner_summary.json", delta_summary)

    status = _status_for(execute=execute, blockers=blockers, delta_summary=delta_summary)
    summary = {
        "run_id": run_id,
        "mode": "explicit_mainnet_multiphase_topup_execution",
        "environment": "mainnet",
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "artifact_root": str(run_root),
        "config": str(getattr(args, "config", "") or ""),
        "plan_artifact": str(getattr(args, "plan_artifact", "") or ""),
        "source_plan_hash": source_plan.get("plan_hash"),
        "topup_plan_hash": topup_plan_hash,
        "source_plan_run_id": dict(source_plan.get("run_summary") or {}).get("run_id"),
        "required_confirmation": required_topup_confirmation,
        "delta_required_confirmation": required_delta_confirmation,
        "execute_requested": bool(execute),
        "mainnet_order_submission_authorized": bool(execute and not blockers),
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "expected_reserve_usdt": float(getattr(args, "expected_reserve_usdt", 150.0) or 150.0),
        "topup_preflight_status": topup_preflight.get("status"),
        "topup_gate_status": topup_preflight.get("capital_topup_gate_status"),
        "margin_cushion_gate_status": topup_preflight.get("margin_cushion_gate_status"),
        "execution_stage": topup_preflight.get("execution_stage"),
        "planned_delta_order_count": int(topup_preflight.get("planned_delta_order_count") or 0),
        "target_leg_count": int(topup_preflight.get("target_leg_count") or 0),
        "executable_entry_leg_count": int(topup_preflight.get("executable_entry_leg_count") or 0),
        "submitted_order_count": int(delta_summary.get("submitted_order_count") or 0),
        "fill_count": int(delta_summary.get("fill_count") or 0),
        "delta_runner_status": delta_summary.get("status"),
        "delta_runner_artifact_root": delta_summary.get("artifact_root"),
    }
    write_json(run_root / "run_summary.json", summary)
    state_store.write_json_row("run_summaries", "run_id", run_id, summary)
    state_store.record_live_artifact(
        run_id=run_id,
        artifact_type="mainnet_multiphase_topup_execution",
        artifact_id=f"{run_id}:topup_execution",
        payload=summary,
    )
    return summary, 0 if status in {"mainnet_multiphase_topup_execution_ready", "mainnet_multiphase_topup_orders_submitted"} else 2


def _topup_source_preflight(
    *,
    source_plan: dict[str, Any],
    payload: dict[str, Any],
    expected_reserve_usdt: float,
    allowed_delta_classifications: set[str],
) -> dict[str, Any]:
    plan_root = Path(str(source_plan.get("plan_root") or ""))
    summary = dict(source_plan.get("run_summary") or {})
    runtime_gate = dict(source_plan.get("runtime_gate_context") or {})
    capital_context = _read_json(plan_root / "capital_allocation_context.json")
    topup_gate = _read_json(plan_root / "capital_topup_gate.json")
    margin_gate = _read_json(plan_root / "margin_cushion_gate.json")
    intents_frame = source_plan.get("intents_frame")
    sizing_frame = source_plan.get("sizing_frame")
    blockers: list[str] = []
    warnings: list[str] = []

    if summary.get("target_engine") != MULTIPHASE_TARGET_ENGINE:
        blockers.append(f"topup_requires_multiphase_target_engine:{summary.get('target_engine') or 'missing'}")
    if runtime_gate.get("target_engine") not in {"", None, MULTIPHASE_TARGET_ENGINE}:
        blockers.append(f"topup_runtime_target_engine_mismatch:{runtime_gate.get('target_engine')}")
    if summary.get("capital_topup_requested") is not True:
        blockers.append("topup_source_plan_not_capital_topup")
    if str(summary.get("capital_topup_gate_status") or "") != "passed":
        blockers.append(f"topup_summary_gate_not_passed:{summary.get('capital_topup_gate_status') or 'missing'}")
    if str(topup_gate.get("status") or "") != "passed":
        blockers.append(f"topup_gate_not_passed:{topup_gate.get('status') or 'missing'}")
    blockers.extend(f"topup_gate_blocker:{item}" for item in list(topup_gate.get("blockers") or []))
    if topup_gate.get("require_balanced_all_or_none") is not True:
        blockers.append("topup_gate_not_all_or_none")
    if str(topup_gate.get("active_execution_phase") or "") != "entry_second":
        blockers.append(f"topup_gate_not_entry_second:{topup_gate.get('active_execution_phase') or 'missing'}")
    if int(topup_gate.get("dust_leg_count") or 0) != 0:
        blockers.append(f"topup_gate_has_dust_legs:{topup_gate.get('dust_leg_count')}")
    if int(topup_gate.get("reduce_like_row_count") or 0) != 0:
        blockers.append(f"topup_gate_has_reduce_like_rows:{topup_gate.get('reduce_like_row_count')}")
    if int(topup_gate.get("incomplete_entry_leg_count") or 0) != 0:
        blockers.append(f"topup_gate_has_incomplete_entries:{topup_gate.get('incomplete_entry_leg_count')}")
    if int(topup_gate.get("disallowed_row_count") or 0) != 0:
        blockers.append(f"topup_gate_has_disallowed_rows:{topup_gate.get('disallowed_row_count')}")
    if int(topup_gate.get("planned_delta_order_count") or 0) <= 0:
        blockers.append("topup_gate_has_no_planned_orders")
    if int(topup_gate.get("planned_delta_order_count") or 0) != int(topup_gate.get("target_leg_count") or 0):
        blockers.append("topup_gate_order_count_not_equal_target_leg_count")
    if int(topup_gate.get("planned_delta_order_count") or 0) != int(topup_gate.get("executable_entry_leg_count") or 0):
        blockers.append("topup_gate_order_count_not_equal_executable_entry_leg_count")

    if str(margin_gate.get("status") or "") != "passed" or margin_gate.get("passed") is not True:
        blockers.append(f"topup_margin_cushion_not_passed:{margin_gate.get('status') or 'missing'}")
    blockers.extend(f"topup_margin_blocker:{item}" for item in list(margin_gate.get("blockers") or []))

    config_topup = dict(payload.get("capital_topup") or {})
    if config_topup.get("enabled") is not True:
        blockers.append("topup_execution_config_capital_topup_disabled")
    if config_topup.get("live_execution_enabled") is not True:
        blockers.append("topup_execution_config_live_execution_not_enabled")
    configured_reserve = _float(config_topup.get("reserve_available_balance_usdt"))
    actual_reserve = _float(capital_context.get("reserve_available_balance_usdt"))
    if abs(configured_reserve - float(expected_reserve_usdt)) > 1e-9:
        blockers.append(f"topup_config_reserve_mismatch:{configured_reserve}!={float(expected_reserve_usdt)}")
    if abs(actual_reserve - float(expected_reserve_usdt)) > 1e-9:
        blockers.append(f"topup_plan_reserve_mismatch:{actual_reserve}!={float(expected_reserve_usdt)}")
    if str(capital_context.get("status") or "") != "capital_topup_resolved":
        blockers.append(f"topup_capital_not_resolved:{capital_context.get('status') or 'missing'}")
    if _float(capital_context.get("additional_allocated_capital_usdt")) <= 0:
        blockers.append("topup_no_additional_allocated_capital")
    resolved = _float(capital_context.get("resolved_allocated_capital_usdt"))
    baseline = _float(capital_context.get("baseline_allocated_capital_usdt"))
    if resolved <= baseline:
        blockers.append(f"topup_resolved_not_above_baseline:{resolved}<={baseline}")
    expected_resolved = max(
        0.0,
        (_float(capital_context.get("total_wallet_balance_usdt")) - float(expected_reserve_usdt))
        * _float(capital_context.get("sizing_multiplier")),
    ) - _float(capital_context.get("gross_notional_safety_buffer_usdt"))
    if abs(resolved - expected_resolved) > 1e-6:
        blockers.append(f"topup_resolved_formula_mismatch:{resolved}!={expected_resolved}")

    blockers.extend(
        _intent_frame_blockers(
            intents_frame=intents_frame,
            sizing_frame=sizing_frame,
            allowed_delta_classifications=allowed_delta_classifications,
        )
    )
    warnings.extend(str(item) for item in list(capital_context.get("warnings") or []))
    warnings.extend(str(item) for item in list(topup_gate.get("warnings") or []))
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "target_engine": summary.get("target_engine"),
        "capital_topup_gate_status": topup_gate.get("status"),
        "margin_cushion_gate_status": margin_gate.get("status"),
        "execution_stage": source_plan.get("execution_stage"),
        "planned_delta_order_count": int(summary.get("planned_delta_order_count") or 0),
        "target_leg_count": int(topup_gate.get("target_leg_count") or 0),
        "executable_entry_leg_count": int(topup_gate.get("executable_entry_leg_count") or 0),
        "reserve_available_balance_usdt": actual_reserve,
        "resolved_allocated_capital_usdt": resolved,
        "additional_allocated_capital_usdt": _float(capital_context.get("additional_allocated_capital_usdt")),
        "post_plan_available_balance_usdt": _float(margin_gate.get("post_plan_available_balance_usdt")),
        "post_plan_available_balance_ratio": _float(margin_gate.get("post_plan_available_balance_ratio")),
        "allowed_delta_classifications": sorted(allowed_delta_classifications),
    }


def _intent_frame_blockers(
    *,
    intents_frame: Any,
    sizing_frame: Any,
    allowed_delta_classifications: set[str],
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(intents_frame, pd.DataFrame) or intents_frame.empty:
        return ["topup_execution_plan_has_no_intents"]
    row_symbols: list[str] = []
    for _, row in intents_frame.iterrows():
        symbol = str(row.get("symbol") or "unknown")
        row_symbols.append(symbol)
        phase = str(row.get("execution_phase") or "").strip().lower()
        classification = str(row.get("delta_classification") or "").strip().lower()
        if phase != "entry_second":
            blockers.append(f"topup_intent_not_entry_second:{symbol}:{phase or 'missing'}")
        if _bool(row.get("reduce_only")):
            blockers.append(f"topup_intent_reduce_only:{symbol}")
        if classification not in allowed_delta_classifications:
            blockers.append(f"topup_intent_delta_classification_not_allowed:{symbol}:{classification or 'missing'}")
        if _float(row.get("quantity")) <= 0:
            blockers.append(f"topup_intent_non_positive_quantity:{symbol}")
    if len(row_symbols) != len(set(row_symbols)):
        blockers.append("topup_execution_plan_duplicate_symbols")
    if isinstance(sizing_frame, pd.DataFrame) and not sizing_frame.empty and "blockers" in sizing_frame.columns:
        blocked = sizing_frame.loc[sizing_frame["blockers"].fillna("").astype(str).str.strip().ne("")]
        for _, row in blocked.iterrows():
            blockers.append(f"topup_order_sizing_blocked:{row.get('symbol')}:{row.get('blockers')}")
    return blockers


def _execute_confirmation_blockers(
    args: argparse.Namespace,
    *,
    payload: dict[str, Any],
    required_confirmation: str,
) -> list[str]:
    blockers: list[str] = []
    if not bool(getattr(args, "operator_enable_mainnet_topup_for_this_run", False)):
        blockers.append("missing_operator_enable_mainnet_topup_for_this_run")
    if not bool(getattr(args, "i_understand_this_places_real_mainnet_topup_orders", False)):
        blockers.append("missing_mainnet_topup_order_understanding_flag")
    if str(getattr(args, "confirm_mainnet_topup_execution", "") or "").strip() != required_confirmation:
        blockers.append("missing_exact_mainnet_topup_confirmation")
    if dict(payload.get("capital_topup") or {}).get("live_execution_enabled") is not True:
        blockers.append("topup_live_execution_disabled_in_config")
    return blockers


def _delta_args(
    args: argparse.Namespace,
    *,
    execute: bool,
    delta_confirmation: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        config=str(getattr(args, "config", "") or ""),
        plan_artifact=str(getattr(args, "plan_artifact", "") or ""),
        execute_mainnet_delta_orders=bool(execute),
        operator_enable_mainnet_delta_for_this_run=bool(execute),
        i_understand_this_places_real_mainnet_delta_orders=bool(execute),
        i_understand_daily_loss_budget_is_review_only=False,
        i_understand_daily_realized_pnl_gate_is_active=False,
        confirm_mainnet_delta_execution=str(delta_confirmation if execute else ""),
        position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
        ignore_heartbeat_run_id=str(getattr(args, "ignore_heartbeat_run_id", "") or ""),
    )


def _status_for(*, execute: bool, blockers: list[str], delta_summary: dict[str, Any]) -> str:
    if blockers:
        return "blocked"
    delta_status = str(delta_summary.get("status") or "")
    if execute and delta_status == "mainnet_delta_orders_submitted":
        return "mainnet_multiphase_topup_orders_submitted"
    if not execute and delta_status == "mainnet_delta_execution_ready":
        return "mainnet_multiphase_topup_execution_ready"
    return f"unexpected_delta_status:{delta_status or 'missing'}"


def _required_topup_confirmation(*, plan_hash: str, reserve_usdt: float) -> str:
    digest = str(plan_hash or "missing")[:16]
    reserve_token = f"{float(reserve_usdt):.8f}".rstrip("0").rstrip(".")
    return (
        f"{CONFIRMATION_PREFIX}:PLAN_SHA256={digest}:RESERVE={reserve_token}:"
        "ENTRY_SECOND:ALL_OR_NONE:MARGIN_PASSED:NO_REDUCE:NO_DUST:DELTA_ONLY:NO_RECURRING:NO_DAILY_PNL_GATE"
    )


def _topup_plan_artifact_hash(plan_root: Path) -> str:
    import hashlib

    names = [
        "run_summary.json",
        "runtime_gate_context.json",
        "execution_plan.json",
        "execution_plan.csv",
        "order_sizing_report.csv",
        "risk_gate.json",
        "target_portfolio.json",
        "current_positions.csv",
        "capital_allocation_context.json",
        "capital_topup_gate.json",
        "margin_cushion_gate.json",
        # Bind the frozen-frontier verdict + resolved PIT universe into the topup confirmation
        # token too (defence-in-depth; the delta executor already binds both). Both are written by
        # the plan runner and skipped here when absent => fixed/frontier-off plans hash unchanged.
        FRONTIER_PLAN_ARTIFACT,
        LIVE_UNIVERSE_ARTIFACT,
    ]
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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "blockers": [f"missing_file:{path.name}"]}
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _csv_set(raw: Any) -> set[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(item) for item in raw]
    else:
        values = str(raw or "").split(",")
    output = {item.strip().lower() for item in values if item.strip()}
    return output or set(DEFAULT_ALLOWED_DELTA_CLASSIFICATIONS)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
