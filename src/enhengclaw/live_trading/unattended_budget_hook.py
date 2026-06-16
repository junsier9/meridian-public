"""Wiring helpers that connect the unattended budget store to the core loop — DRAFT.

These are the testable decision functions the live cycle calls. The cycle itself
(mainnet_core_loop_runner._run_cycle) does only file IO + list-extension; all the
logic that could fail open lives here so it can be unit-tested with a temp-DB
store and synthetic plan/execution artifacts.

Contract enforced here (from the adversarial review):
  - projected turnover: sum |rounded_notional_usdt| over the dry-run planned
    orders; if there ARE planned orders but the sum is 0, return None so the gate
    fails closed (never coerce unknown turnover to 0.0).
  - realized turnover: max(sum |fill notional|, sum |submitted planned notional|)
    so a partial fill that left orders on the exchange still debits.
  - pre-submit: fail closed on any unreconciled prior reservation (orphan from a
    crashed in-flight cycle) BEFORE reserving this cycle, then reserve-before-submit.
  - the budget is only consulted when the gate is enabled in config AND the cycle
    is otherwise about to submit (execute_live_delta, no other blocker), so the
    ~50 existing attended/canary flows are untouched.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from enhengclaw.live_trading.config import resolve_repo_path
from enhengclaw.live_trading.unattended_budget_gate import BudgetEpoch
from enhengclaw.live_trading.unattended_budget_store import UnattendedBudgetStore


CONFIG_FLAG = "unattended_budget_gate_enabled"
ORPHAN_BLOCKER = "unattended_budget_unreconciled_prior_cycle"
PER_ORDER_GATE_FLAG = "per_order_notional_gate_enabled"
PER_ORDER_MULTIPLIER_KEY = "per_order_notional_hard_multiplier"
DEFAULT_PER_ORDER_MULTIPLIER = 1.5


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def budget_gate_enabled(payload: dict[str, Any]) -> bool:
    return _as_bool(dict(payload.get("core_loop") or {}).get(CONFIG_FLAG), default=False)


def budget_store_from_payload(payload: dict[str, Any]) -> UnattendedBudgetStore:
    sqlite_path = str(dict(payload.get("state") or {}).get("sqlite_path") or "")
    return UnattendedBudgetStore(resolve_repo_path(sqlite_path))


def per_order_gate_enabled(payload: dict[str, Any]) -> bool:
    return _as_bool(dict(payload.get("risk") or {}).get(PER_ORDER_GATE_FLAG), default=False)


def per_order_hard_multiplier(payload: dict[str, Any]) -> float:
    value = _finite(dict(payload.get("risk") or {}).get(PER_ORDER_MULTIPLIER_KEY))
    return value if value is not None and value > 0.0 else DEFAULT_PER_ORDER_MULTIPLIER


def resolved_per_order_notional_cap(
    payload: dict[str, Any],
    capital_allocation_context: dict[str, Any],
    *,
    capital_topup_selected: bool,
) -> float | None:
    """Resolve the per-order notional cap the SAME way the plan stage does
    (mainnet_rebalance_plan_runner._risk_payload_plan_only): the larger of the
    static config cap and resolved_capital * max_order_weight_cap. Returns the
    resolved value (~weight-cap notional, e.g. ~1034 on this book), NOT the
    static 600, so legitimate orders are not false-positived."""
    risk = dict(payload.get("risk") or {})
    static = _finite(risk.get("max_order_notional_usdt"))
    resolved = _finite(dict(capital_allocation_context or {}).get("resolved_allocated_capital_usdt"))
    cap_cfg = dict(payload.get("capital_topup") or {}) if capital_topup_selected else dict(payload.get("capital") or {})
    weight = _finite(cap_cfg.get("max_order_weight_cap"))
    if weight is None:
        weight = _finite(dict(payload.get("capital_topup") or {}).get("max_order_weight_cap"))
    candidates: list[float] = []
    if static is not None and static > 0.0:
        candidates.append(static)
    if resolved is not None and resolved > 0.0 and weight is not None and weight > 0.0:
        candidates.append(resolved * weight)
    return max(candidates) if candidates else None


def projected_turnover_usdt(planned_orders_json: dict[str, Any]) -> float | None:
    """Sum |rounded_notional_usdt| over planned orders. Returns None (fail closed)
    if a row's notional is unreadable, or if there are planned orders but the
    total is 0 (a submitting plan must never project zero turnover)."""
    rows = list(planned_orders_json.get("rows") or [])
    count = int(planned_orders_json.get("row_count") or len(rows))
    total = 0.0
    for row in rows:
        notional = _finite(row.get("rounded_notional_usdt"))
        if notional is None:
            return None
        total += abs(notional)
    if count > 0 and total <= 0.0:
        return None
    return total


def realized_turnover_usdt(execution_json: dict[str, Any]) -> float | None:
    """max(sum |fill notional_usdt|, sum |submitted planned_rounded_notional_usdt|).

    Using the max means a partial fill that left an order resting on the exchange
    is still charged at least its submitted notional. Returns None when neither
    list carries usable notionals (the store then keeps the projected debit)."""
    fills = list(execution_json.get("fills") or [])
    submitted = list(execution_json.get("submitted_orders") or [])
    fill_total = _sum_abs(fills, "notional_usdt") if fills else None
    sub_total = _sum_abs(submitted, "planned_rounded_notional_usdt") if submitted else None
    candidates = [value for value in (fill_total, sub_total) if value is not None]
    return max(candidates) if candidates else None


def _sum_abs(rows: list[dict[str, Any]], field: str) -> float:
    total = 0.0
    for row in rows:
        notional = _finite(row.get(field))
        if notional is not None:
            total += abs(notional)
    return total


def reservation_key(epoch_id: str, plan_ref: str, cycle_index: int) -> str:
    """Stable per planned cycle. Idempotency PK for a single reserve attempt;
    cross-fire safety comes from the orphan check, not this key."""
    return f"{epoch_id}:{plan_ref}:{int(cycle_index)}"


def pre_submit_budget_blockers(
    store: UnattendedBudgetStore,
    *,
    enabled: bool,
    epoch: BudgetEpoch | None,
    projected_turnover: float | None,
    run_id: str,
    reservation_key: str,
    now: datetime,
) -> tuple[list[str], dict[str, Any]]:
    """Orphan-check then reserve-before-submit. Returns (blockers, result).

    A non-empty blocker list must be cascaded into the cycle's blocker list so
    disarm_on_blocker halts the machine. "reserved"/"already_reserved" are the
    only results that permit the subsequent live submit.
    """
    if not enabled:
        return [], {"status": "disabled", "passed": True}
    if epoch is None:
        return ["unattended_budget_no_open_epoch"], {"status": "blocked", "passed": False}
    if store.has_unreconciled_reservation(epoch_id=epoch.epoch_id):
        return [ORPHAN_BLOCKER], {"status": "blocked_orphan", "passed": False, "epoch_id": epoch.epoch_id}
    result = store.reserve(
        epoch_id=epoch.epoch_id,
        reservation_key=reservation_key,
        run_id=run_id,
        projected_turnover_usdt=projected_turnover,
        now_utc=now,
    )
    if str(result.get("status")) in {"reserved", "already_reserved"}:
        return [], result
    return sorted(set(result.get("blockers") or ["unattended_budget_reserve_rejected"])), result


def reserved_ok(pre_submit_result: dict[str, Any]) -> bool:
    return str(pre_submit_result.get("status")) in {"reserved", "already_reserved"}


def reconcile_or_block_realized(
    *, orders_submitted: int, realized_turnover: float | None
) -> tuple[bool, str | None]:
    """B1: decide whether the post-submit budget reconcile may proceed.

    If orders WERE submitted but the realized turnover is unmeasurable (None — e.g. the
    execution artifact is missing/corrupt after a crash), the reconcile MUST be skipped: a
    silent reconcile would mark the reservation terminal with only the projected debit, clearing
    the orphan flag and under-counting the budget — bypassing the crash-safety. Instead leave the
    reservation as an orphan (so the next cycle's pre-submit orphan check also fails closed) and
    raise a blocker that disarms this cycle. When no orders were submitted, realized=None is the
    benign over-counted case (reserve already debited projected) and reconcile proceeds.

    Returns ``(may_reconcile, blocker_or_None)``.
    """
    if int(orders_submitted) > 0 and realized_turnover is None:
        return False, "unattended_budget_realized_turnover_unmeasured"
    return True, None


def post_submit_reconcile(
    store: UnattendedBudgetStore,
    *,
    reserved: bool,
    reservation_key: str,
    realized_turnover: float | None,
    now: datetime,
) -> dict[str, Any]:
    """After execution, reconcile the reservation to realized turnover (bumps the
    ledger UP only) and clear the orphan flag. No-op if we never reserved."""
    if not reserved:
        return {"status": "skipped_not_reserved"}
    return store.reconcile_reservation(
        reservation_key=reservation_key,
        realized_turnover_usdt=realized_turnover,
        now_utc=now,
    )
