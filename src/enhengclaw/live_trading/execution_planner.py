from __future__ import annotations

import hashlib
import math
from decimal import Decimal, ROUND_DOWN
from typing import Any

import pandas as pd

from enhengclaw.live_trading.models import ExecutionPlan, OrderIntent, RiskGateResult, TargetPortfolio


NOOP_EXECUTION_PHASES = {"noop", "dust_noop", "deadband_noop"}
DEADBAND_DEFAULT_DELTA_CLASSIFICATIONS = {"increase_same_side", "reduce_same_side"}
DEADBAND_DEFAULT_EXEMPT_CLASSIFICATIONS = {"new_entry", "flip_position", "exit_stale_symbol", "exit_target_removed"}


def build_execution_plan(
    portfolio: TargetPortfolio,
    risk_gate: RiskGateResult,
    *,
    mode: str,
    current_positions: dict[str, float] | None = None,
    mark_prices: dict[str, float] | None = None,
    symbol_filters: dict[str, dict[str, Any]] | None = None,
    execution_deadband: dict[str, Any] | None = None,
    target_position_overrides: dict[str, float] | None = None,
    target_reference_prices: dict[str, float] | None = None,
    max_slippage_bps: float = 20.0,
    allow_testnet_order_submission: bool = False,
    allow_live_order_submission: bool = False,
) -> ExecutionPlan:
    normalized_mode = str(mode or "plan_only").strip().lower() or "plan_only"
    plan_id = f"{portfolio.portfolio_id}:plan:{normalized_mode}"
    blockers: list[str] = []
    intents: list[OrderIntent] = []
    if not risk_gate.passed:
        blockers.append("risk_gate_not_passed")
    if normalized_mode == "testnet" and not allow_testnet_order_submission:
        blockers.append("testnet_order_submission_not_implemented_in_phase1")
    if normalized_mode == "live" and not allow_live_order_submission:
        blockers.append(f"{normalized_mode}_order_submission_not_implemented_in_phase1")
    sizing_rows = build_order_sizing_rows(
        portfolio,
        mode=normalized_mode,
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
        execution_deadband=execution_deadband,
        target_position_overrides=target_position_overrides,
        target_reference_prices=target_reference_prices,
    )
    active_phase = _active_execution_phase(sizing_rows)
    phase_counts = _phase_counts(sizing_rows)
    deferred_phase_counts: dict[str, int] = {}
    for row in sorted(sizing_rows, key=lambda item: (int(item.get("phase_priority") or 99), int(item.get("seq") or 0))):
        symbol = str(row["symbol"])
        row_blockers = _split_blockers(str(row.get("blockers") or ""))
        row_phase = str(row.get("execution_phase") or "")
        if row_phase != "dust_noop":
            blockers.extend(row_blockers)
        if row_phase == "entry_second" and active_phase == "reduce_first" and not row_blockers:
            deferred_phase_counts[row_phase] = int(deferred_phase_counts.get(row_phase, 0)) + 1
            continue
        if _truthy(row.get("no_order_required")) or row_phase in NOOP_EXECUTION_PHASES or row_blockers:
            continue
        intent_id = f"{plan_id}:{symbol}:{int(row['seq'])}"
        intents.append(
            OrderIntent(
                intent_id=intent_id,
                portfolio_id=portfolio.portfolio_id,
                symbol=symbol,
                side=str(row["side"]),
                position_side="BOTH",
                order_type="MARKET",
                quantity=float(row["rounded_quantity"]),
                reduce_only=bool(row["reduce_only"]),
                target_position_amt=float(row.get("order_target_position_amt", row["target_position_amt"])),
                current_position_amt=float(row["current_position_amt"]),
                delta_position_amt=float(row.get("order_delta_position_amt", row["delta_position_amt"])),
                max_slippage_bps=float(max_slippage_bps),
                client_order_id=_client_order_id(
                    mode=normalized_mode,
                    portfolio_id=portfolio.portfolio_id,
                    symbol=symbol,
                    seq=int(row["seq"]),
                ),
                execution_phase=row_phase,
                delta_classification=str(row.get("delta_classification") or ""),
                final_target_position_amt=float(row.get("final_target_position_amt", row["target_position_amt"])),
                second_phase_required=bool(row.get("second_phase_required")),
            )
        )
    status = "ok" if not blockers else "blocked"
    return ExecutionPlan(
        plan_id=plan_id,
        portfolio_id=portfolio.portfolio_id,
        mode=normalized_mode,
        status=status,
        blockers=sorted(set(blockers)),
        intents=intents,
        active_execution_phase=active_phase,
        phase_counts=phase_counts,
        deferred_phase_counts=deferred_phase_counts,
    )


def build_order_sizing_report(
    portfolio: TargetPortfolio,
    *,
    mode: str,
    current_positions: dict[str, float] | None = None,
    mark_prices: dict[str, float] | None = None,
    symbol_filters: dict[str, dict[str, Any]] | None = None,
    execution_deadband: dict[str, Any] | None = None,
    target_position_overrides: dict[str, float] | None = None,
    target_reference_prices: dict[str, float] | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        build_order_sizing_rows(
            portfolio,
            mode=mode,
            current_positions=current_positions,
            mark_prices=mark_prices,
            symbol_filters=symbol_filters,
            execution_deadband=execution_deadband,
            target_position_overrides=target_position_overrides,
            target_reference_prices=target_reference_prices,
        )
    )


def summarize_order_sizing_report(report: pd.DataFrame | list[dict[str, Any]], *, allocated_capital_usdt: float) -> dict[str, Any]:
    rows = report.to_dict(orient="records") if isinstance(report, pd.DataFrame) else list(report)
    blockers: list[str] = []
    target_rows = [row for row in rows if bool(row.get("has_target"))]
    for row in rows:
        blockers.extend(_split_blockers(str(row.get("blockers") or "")))
    min_capital_rows = [
        row
        for row in target_rows
        if _is_finite_number(row.get("min_allocated_capital_usdt_for_target_weight"))
    ]
    max_min_capital = max(
        [float(row["min_allocated_capital_usdt_for_target_weight"]) for row in min_capital_rows],
        default=0.0,
    )
    limiting = [
        {
            "symbol": str(row.get("symbol") or ""),
            "target_weight": float(row.get("target_weight") or 0.0),
            "target_notional_usdt": float(row.get("target_notional_usdt") or 0.0),
            "min_executable_notional_usdt": float(row.get("min_executable_notional_usdt") or 0.0),
            "min_allocated_capital_usdt_for_target_weight": float(
                row.get("min_allocated_capital_usdt_for_target_weight") or 0.0
            ),
            "blockers": str(row.get("blockers") or ""),
        }
        for row in min_capital_rows
        if abs(float(row["min_allocated_capital_usdt_for_target_weight"]) - max_min_capital) <= 1e-9
    ]
    non_executable_targets = [
        str(row.get("symbol") or "")
        for row in target_rows
        if str(row.get("blockers") or "").strip()
    ]
    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "allocated_capital_usdt": float(allocated_capital_usdt),
        "target_row_count": int(len(target_rows)),
        "order_row_count": int(sum(not _truthy(row.get("no_order_required")) for row in rows)),
        "executable_order_count": int(
            sum(not _truthy(row.get("no_order_required")) and not str(row.get("blockers") or "").strip() for row in rows)
        ),
        "non_executable_target_count": int(len(non_executable_targets)),
        "non_executable_target_symbols": non_executable_targets,
        "min_allocated_capital_usdt_for_all_targets": float(max_min_capital),
        "additional_allocated_capital_needed_usdt": float(max(0.0, max_min_capital - float(allocated_capital_usdt))),
        "limiting_symbols": limiting,
    }


def summarize_dust_residual_order_sizing(report: pd.DataFrame | list[dict[str, Any]]) -> dict[str, Any]:
    rows = report.to_dict(orient="records") if isinstance(report, pd.DataFrame) else list(report)
    blocked_rows: list[dict[str, Any]] = []
    dust_blockers: list[str] = []
    hard_blockers: list[str] = []
    executable_order_count = 0
    dust_symbols: list[str] = []
    for row in rows:
        blockers = _split_blockers(str(row.get("blockers") or ""))
        if _truthy(row.get("no_order_required")):
            continue
        if not blockers:
            executable_order_count += 1
            continue
        blocked_rows.append(row)
        symbol = str(row.get("symbol") or "")
        dust_blockers.extend(blockers)
        if not _all_min_order_blockers(blockers):
            hard_blockers.extend(blockers)
            continue
        current_amt = float(row.get("current_position_amt") or 0.0)
        target_amt = float(row.get("target_position_amt") or 0.0)
        same_direction_residual = abs(current_amt) > 1e-12 and current_amt * target_amt > 0.0
        stale_position_residual = abs(current_amt) > 1e-12 and abs(target_amt) <= 1e-12
        if same_direction_residual or stale_position_residual:
            dust_symbols.append(symbol)
        else:
            hard_blockers.extend(blockers)
    dust_only = bool(blocked_rows) and executable_order_count == 0 and not hard_blockers and len(dust_symbols) == len(blocked_rows)
    return {
        "is_dust_residual_only": bool(dust_only),
        "blocked_row_count": int(len(blocked_rows)),
        "executable_order_count": int(executable_order_count),
        "dust_symbols": sorted(set(dust_symbols)),
        "dust_blockers": sorted(set(dust_blockers)),
        "hard_blockers": sorted(set(hard_blockers)),
    }


def build_order_sizing_rows(
    portfolio: TargetPortfolio,
    *,
    mode: str,
    current_positions: dict[str, float] | None = None,
    mark_prices: dict[str, float] | None = None,
    symbol_filters: dict[str, dict[str, Any]] | None = None,
    execution_deadband: dict[str, Any] | None = None,
    target_position_overrides: dict[str, float] | None = None,
    target_reference_prices: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    normalized_mode = str(mode or "plan_only").strip().lower() or "plan_only"
    current = {str(symbol): float(amount) for symbol, amount in dict(current_positions or {}).items()}
    prices = dict(mark_prices or {})
    filters = dict(symbol_filters or {})
    frozen_targets = {
        str(symbol): float(amount)
        for symbol, amount in dict(target_position_overrides or {}).items()
        if _is_finite_number(amount)
    }
    reference_prices = {
        str(symbol): float(price)
        for symbol, price in dict(target_reference_prices or {}).items()
        if _is_finite_number(price)
    }
    target_by_symbol = {position.usdm_symbol: position for position in portfolio.positions}
    deadband_config = _normalize_execution_deadband(execution_deadband)
    ordered_symbols = [position.usdm_symbol for position in portfolio.positions]
    ordered_symbols.extend(
        symbol for symbol in sorted(current) if symbol not in target_by_symbol and abs(float(current.get(symbol, 0.0) or 0.0)) > 1e-12
    )
    rows: list[dict[str, Any]] = []
    for seq, symbol in enumerate(ordered_symbols, start=1):
        position = target_by_symbol.get(symbol)
        price = float(prices.get(symbol, 0.0) or 0.0)
        target_notional = float(position.target_notional_usdt) if position is not None else 0.0
        target_weight = float(position.target_weight) if position is not None else 0.0
        target_reference_price = float(reference_prices.get(symbol, price) or 0.0)
        current_amt = float(current.get(symbol, 0.0) or 0.0)
        blockers: list[str] = []
        target_amt = 0.0
        delta_amt = 0.0
        raw_abs_delta_qty = 0.0
        quantity = 0.0
        rounded_notional = 0.0
        side = ""
        reduce_only = False
        delta_classification = "blocked"
        execution_phase = "blocked"
        phase_priority = 99
        order_target_amt = 0.0
        order_delta_amt = 0.0
        final_target_amt = 0.0
        final_delta_amt = 0.0
        second_phase_required = False
        deadband_applied = False
        deadband_threshold_notional = 0.0
        deadband_candidate_notional = 0.0
        deadband_raw_delta_notional = 0.0
        deadband_original_delta_classification = ""
        deadband_original_execution_phase = ""
        deadband_reason = ""
        symbol_filter = filters.get(symbol, {})
        step_size = float(symbol_filter.get("step_size", 0.0) or 0.0)
        min_qty = float(symbol_filter.get("min_qty", 0.0) or 0.0)
        min_notional = float(symbol_filter.get("min_notional", 0.0) or 0.0)
        min_qty_notional = 0.0
        min_executable_notional = float(min_notional)
        min_allocated = 0.0
        no_order_required = False
        if price <= 0.0 or not math.isfinite(price):
            blockers.append(f"missing_mark_price:{symbol}")
        else:
            if position is not None and symbol in frozen_targets:
                target_amt = float(frozen_targets[symbol])
            else:
                target_amt = (target_notional / price) * (
                    1.0 if target_weight > 0.0 else -1.0 if target_weight < 0.0 else 0.0
                )
            final_target_amt = target_amt
            final_delta_amt = target_amt - current_amt
            delta_amt = final_delta_amt
            classification = _classify_rebalance_delta(current_amt=current_amt, target_amt=target_amt, has_target=position is not None)
            delta_classification = str(classification["delta_classification"])
            execution_phase = str(classification["execution_phase"])
            phase_priority = int(classification["phase_priority"])
            order_target_amt = float(classification["order_target_position_amt"])
            order_delta_amt = float(classification["order_delta_position_amt"])
            second_phase_required = bool(classification["second_phase_required"])
            no_order_required = execution_phase == "noop"
            side = "BUY" if order_delta_amt > 0.0 else "SELL" if order_delta_amt < 0.0 else ""
            reduce_only = bool(classification["reduce_only"])
            raw_abs_delta_qty = abs(order_delta_amt)
            quantity = _round_step(raw_abs_delta_qty, str(symbol_filter.get("step_size") or "0.000001"))
            rounded_notional = float(quantity * price)
            min_qty_notional = float(min_qty * price)
            min_executable_notional = float(max(min_notional, min_qty_notional))
            if abs(target_weight) > 1e-12:
                min_allocated = float(min_executable_notional / abs(target_weight))
            if not no_order_required:
                if quantity <= 0.0 or quantity < min_qty:
                    blockers.append(f"quantity_below_min:{symbol}")
                if quantity * price < min_notional:
                    blockers.append(f"notional_below_min:{symbol}")
            if _is_dust_residual_row(
                blockers=blockers,
                current_amt=current_amt,
                target_amt=target_amt,
                delta_classification=delta_classification,
            ):
                delta_classification = "dust_residual"
                execution_phase = "dust_noop"
                phase_priority = 90
            deadband = _execution_deadband_decision(
                config=deadband_config,
                blockers=blockers,
                no_order_required=no_order_required,
                current_amt=current_amt,
                target_amt=target_amt,
                price=price,
                allocated_capital_usdt=float(portfolio.allocated_capital_usdt),
                min_executable_notional=min_executable_notional,
                rounded_notional=rounded_notional,
                order_delta_amt=order_delta_amt,
                delta_classification=delta_classification,
                execution_phase=execution_phase,
            )
            if deadband is not None:
                deadband_applied = True
                deadband_threshold_notional = float(deadband["threshold_notional_usdt"])
                deadband_candidate_notional = float(deadband["candidate_notional_usdt"])
                deadband_raw_delta_notional = float(deadband["raw_delta_notional_usdt"])
                deadband_original_delta_classification = str(deadband["original_delta_classification"])
                deadband_original_execution_phase = str(deadband["original_execution_phase"])
                deadband_reason = str(deadband["reason"])
                delta_classification = "rebalance_deadband"
                execution_phase = "deadband_noop"
                phase_priority = 85
                order_target_amt = float(current_amt)
                order_delta_amt = 0.0
                raw_abs_delta_qty = 0.0
                quantity = 0.0
                rounded_notional = 0.0
                side = ""
                reduce_only = False
                no_order_required = True
        rows.append(
            {
                "seq": int(seq),
                "mode": normalized_mode,
                "portfolio_id": portfolio.portfolio_id,
                "symbol": symbol,
                "has_target": position is not None,
                "subject": "" if position is None else position.subject,
                "selection_reason": "" if position is None else position.selection_reason,
                "target_side": "" if position is None else position.side,
                "side": side,
                "target_weight": float(target_weight),
                "target_notional_usdt": float(target_notional),
                "mark_price": float(price),
                "target_reference_price": float(target_reference_price),
                "target_position_frozen": bool(position is not None and symbol in frozen_targets),
                "current_position_amt": float(current_amt),
                "target_position_amt": float(target_amt),
                "delta_position_amt": float(delta_amt),
                "final_target_position_amt": float(final_target_amt),
                "final_delta_position_amt": float(final_delta_amt),
                "order_target_position_amt": float(order_target_amt),
                "order_delta_position_amt": float(order_delta_amt),
                "raw_abs_delta_qty": float(raw_abs_delta_qty),
                "step_size": float(step_size),
                "rounded_quantity": float(quantity),
                "min_qty": float(min_qty),
                "min_notional": float(min_notional),
                "rounded_notional_usdt": float(rounded_notional),
                "min_qty_notional_usdt": float(min_qty_notional),
                "min_executable_notional_usdt": float(min_executable_notional),
                "min_allocated_capital_usdt_for_target_weight": float(min_allocated),
                "reduce_only": bool(reduce_only),
                "delta_classification": delta_classification,
                "execution_phase": execution_phase,
                "phase_priority": int(phase_priority),
                "second_phase_required": bool(second_phase_required),
                "no_order_required": bool(no_order_required),
                "executable": bool(not blockers and not no_order_required and execution_phase not in NOOP_EXECUTION_PHASES),
                "deadband_applied": bool(deadband_applied),
                "deadband_threshold_notional_usdt": float(deadband_threshold_notional),
                "deadband_candidate_notional_usdt": float(deadband_candidate_notional),
                "deadband_raw_delta_notional_usdt": float(deadband_raw_delta_notional),
                "deadband_original_delta_classification": deadband_original_delta_classification,
                "deadband_original_execution_phase": deadband_original_execution_phase,
                "deadband_reason": deadband_reason,
                "blockers": ";".join(sorted(set(blockers))),
            }
        )
    return rows


def _round_step(value: float, step_size: str) -> float:
    step = Decimal(str(step_size))
    if step <= 0:
        return float(value)
    quantized = (Decimal(str(value)) / step).to_integral_value(rounding=ROUND_DOWN) * step
    return float(quantized)


def _classify_rebalance_delta(*, current_amt: float, target_amt: float, has_target: bool) -> dict[str, Any]:
    eps = 1e-12
    current_live = abs(float(current_amt)) > eps
    target_live = abs(float(target_amt)) > eps
    final_delta = float(target_amt) - float(current_amt)
    if abs(final_delta) <= eps:
        return _phase(
            delta_classification="no_delta",
            execution_phase="noop",
            phase_priority=80,
            order_target_position_amt=float(current_amt),
            order_delta_position_amt=0.0,
            reduce_only=False,
        )
    if current_live and not target_live:
        return _phase(
            delta_classification="exit_stale_symbol" if not has_target else "exit_target_removed",
            execution_phase="reduce_first",
            phase_priority=10,
            order_target_position_amt=0.0,
            order_delta_position_amt=-float(current_amt),
            reduce_only=True,
        )
    if current_live and target_live and float(current_amt) * float(target_amt) < 0.0:
        return _phase(
            delta_classification="flip_position",
            execution_phase="reduce_first",
            phase_priority=20,
            order_target_position_amt=0.0,
            order_delta_position_amt=-float(current_amt),
            reduce_only=True,
            second_phase_required=True,
        )
    if current_live and target_live:
        if abs(float(target_amt)) < abs(float(current_amt)):
            return _phase(
                delta_classification="reduce_same_side",
                execution_phase="reduce_first",
                phase_priority=30,
                order_target_position_amt=float(target_amt),
                order_delta_position_amt=final_delta,
                reduce_only=True,
            )
        return _phase(
            delta_classification="increase_same_side",
            execution_phase="entry_second",
            phase_priority=60,
            order_target_position_amt=float(target_amt),
            order_delta_position_amt=final_delta,
            reduce_only=False,
        )
    return _phase(
        delta_classification="new_entry",
        execution_phase="entry_second",
        phase_priority=70,
        order_target_position_amt=float(target_amt),
        order_delta_position_amt=final_delta,
        reduce_only=False,
    )


def _phase(
    *,
    delta_classification: str,
    execution_phase: str,
    phase_priority: int,
    order_target_position_amt: float,
    order_delta_position_amt: float,
    reduce_only: bool,
    second_phase_required: bool = False,
) -> dict[str, Any]:
    return {
        "delta_classification": delta_classification,
        "execution_phase": execution_phase,
        "phase_priority": int(phase_priority),
        "order_target_position_amt": float(order_target_position_amt),
        "order_delta_position_amt": float(order_delta_position_amt),
        "reduce_only": bool(reduce_only),
        "second_phase_required": bool(second_phase_required),
    }


def _active_execution_phase(rows: list[dict[str, Any]]) -> str:
    executable = [
        row
        for row in rows
        if not _truthy(row.get("no_order_required"))
        and not _split_blockers(str(row.get("blockers") or ""))
        and str(row.get("execution_phase") or "") not in {*NOOP_EXECUTION_PHASES, "blocked"}
    ]
    if any(str(row.get("execution_phase") or "") == "reduce_first" for row in executable):
        return "reduce_first"
    if any(str(row.get("execution_phase") or "") == "entry_second" for row in executable):
        return "entry_second"
    if any(str(row.get("execution_phase") or "") == "dust_noop" for row in rows):
        return "dust_noop"
    if any(str(row.get("execution_phase") or "") == "deadband_noop" for row in rows):
        return "deadband_noop"
    return "noop"


def _phase_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        phase = str(row.get("execution_phase") or "unknown")
        counts[phase] = int(counts.get(phase, 0)) + 1
    return counts


def _is_dust_residual_row(*, blockers: list[str], current_amt: float, target_amt: float, delta_classification: str) -> bool:
    if not _all_min_order_blockers(blockers):
        return False
    if str(delta_classification) == "new_entry":
        return False
    if str(delta_classification) == "flip_position":
        return False
    current_live = abs(float(current_amt)) > 1e-12
    same_direction_residual = current_live and abs(float(target_amt)) > 1e-12 and float(current_amt) * float(target_amt) > 0.0
    stale_position_residual = current_live and abs(float(target_amt)) <= 1e-12
    return bool(same_direction_residual or stale_position_residual)


def _normalize_execution_deadband(config: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(config or {})
    return {
        "enabled": _truthy(payload.get("enabled")),
        "delta_classifications": _string_set(
            payload.get("delta_classifications", payload.get("classifications")),
            default=DEADBAND_DEFAULT_DELTA_CLASSIFICATIONS,
        ),
        "exempt_delta_classifications": _string_set(
            payload.get("exempt_delta_classifications"),
            default=DEADBAND_DEFAULT_EXEMPT_CLASSIFICATIONS,
        ),
        "fixed_threshold_notional_usdt": _non_negative_float(
            payload.get("same_side_min_delta_notional_usdt", payload.get("min_delta_notional_usdt"))
        ),
        "min_executable_multiplier": _non_negative_float(
            payload.get(
                "min_delta_notional_multiplier_of_min_executable",
                payload.get("min_delta_notional_multiple_of_min_executable"),
            )
        ),
        "min_delta_weight": _non_negative_float(payload.get("min_delta_weight")),
    }


def _execution_deadband_decision(
    *,
    config: dict[str, Any],
    blockers: list[str],
    no_order_required: bool,
    current_amt: float,
    target_amt: float,
    price: float,
    allocated_capital_usdt: float,
    min_executable_notional: float,
    rounded_notional: float,
    order_delta_amt: float,
    delta_classification: str,
    execution_phase: str,
) -> dict[str, Any] | None:
    if not _truthy(config.get("enabled")) or blockers or _truthy(no_order_required):
        return None
    classification = str(delta_classification or "").strip().lower()
    if classification in set(config.get("exempt_delta_classifications") or set()):
        return None
    if classification not in set(config.get("delta_classifications") or set()):
        return None
    phase = str(execution_phase or "").strip().lower()
    if phase not in {"reduce_first", "entry_second"}:
        return None
    if abs(float(current_amt)) <= 1e-12 or abs(float(target_amt)) <= 1e-12:
        return None
    if float(current_amt) * float(target_amt) <= 0.0:
        return None
    raw_delta_notional = abs(float(order_delta_amt)) * float(price)
    candidate_notional = float(rounded_notional) if float(rounded_notional) > 0.0 else raw_delta_notional
    threshold = max(
        float(config.get("fixed_threshold_notional_usdt") or 0.0),
        float(config.get("min_executable_multiplier") or 0.0) * max(0.0, float(min_executable_notional)),
        float(config.get("min_delta_weight") or 0.0) * max(0.0, float(allocated_capital_usdt)),
    )
    if threshold <= 0.0 or candidate_notional <= 0.0 or candidate_notional > threshold:
        return None
    return {
        "threshold_notional_usdt": float(threshold),
        "candidate_notional_usdt": float(candidate_notional),
        "raw_delta_notional_usdt": float(raw_delta_notional),
        "original_delta_classification": classification,
        "original_execution_phase": phase,
        "reason": f"same_side_delta_notional_below_deadband:{candidate_notional}<={threshold}",
    }


def _string_set(value: Any, *, default: set[str]) -> set[str]:
    if value is None:
        return {str(item).strip().lower() for item in default if str(item).strip()}
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, list | tuple | set):
        raw_items = list(value)
    else:
        raw_items = [value]
    items = {str(item).strip().lower() for item in raw_items if str(item).strip()}
    return items or {str(item).strip().lower() for item in default if str(item).strip()}


def _non_negative_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return float(max(0.0, number))


def _client_order_id(*, mode: str, portfolio_id: str, symbol: str, seq: int) -> str:
    digest = hashlib.sha256(f"{mode}:{portfolio_id}:{symbol}:{seq}".encode("utf-8")).hexdigest()[:18]
    return f"hvbal-{mode[:2]}-{digest}-{seq}"


def _split_blockers(value: str) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def _all_min_order_blockers(blockers: list[str]) -> bool:
    prefixes = ("quantity_below_min:", "notional_below_min:")
    return bool(blockers) and all(str(item).startswith(prefixes) for item in blockers)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
