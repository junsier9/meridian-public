"""Fail-closed cumulative budget gate for restricted unattended live_delta.

DRAFT — not yet wired into the live execution path. This module holds only the
PURE evaluation logic (mirroring live_risk_controls.evaluate_margin_cushion_gate):
no DB, no IO, no clock of its own. Persistence (the epoch ledger) lives in
state_store; the hook into the cycle lives in mainnet_core_loop_runner. Keeping
the decision pure makes every fail-closed branch unit-testable.

Purpose: the supervisor pins cycles-per-invocation to 1, but the systemd timer
re-fires (~every 10 min), so an armed flag produces recurring, structurally
unbounded order flow with no aggregate ceiling anywhere in src. This gate is the
ONE thing that bounds the loop across timer re-fires: a persisted epoch carries a
cycle budget, a gross-turnover budget, and a wall-clock max-age, and the gate
fails CLOSED on exhaustion, staleness, or any ambiguity (including non-finite
NaN/inf inputs — IEEE-754 makes every NaN comparison False, so unchecked they
would slip past every guard and silently fail OPEN).

Two independent bounds result:
  - count + turnover budgets  -> "how much" the loop may do per epoch
  - max-age (epoch staleness) -> "how long" one authorization stays valid

The gate is intentionally a no-op unless explicitly enabled, so the ~50 existing
attended / canary / single-run flows are unchanged. The restricted-unattended
profile sets ``core_loop.unattended_budget_gate_enabled: true`` and opens an
epoch via an explicit operator/owner action.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


GATE_CONTRACT_VERSION = "unattended_budget_gate.v1"

EPOCH_STATUS_OPEN = "open"
EPOCH_STATUS_EXHAUSTED = "exhausted"
EPOCH_STATUS_CLOSED = "closed"

_TURNOVER_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class BudgetEpoch:
    """A single owner-authorized unattended budget window.

    Persisted by state_store; this dataclass is the read-side view the gate
    evaluates. All numeric bounds are hard ceilings; consumed_* are running
    totals incremented only on cycles that actually submitted orders.
    """

    epoch_id: str
    created_at_utc: str
    max_live_cycles: int
    max_gross_turnover_usdt: float
    max_age_seconds: int
    consumed_cycles: int
    consumed_turnover_usdt: float
    status: str = EPOCH_STATUS_OPEN


def _coerce_int(value: Any) -> int | None:
    """Coerce to int, returning None on any failure (incl. NaN/inf)."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _coerce_finite_float(value: Any) -> float | None:
    """Coerce to a FINITE float, returning None for NaN/inf/uncoercible.

    This is the linchpin of the fail-closed contract: a non-finite turnover
    value must become None here so downstream guards treat it as corrupt /
    unknown rather than letting a NaN comparison silently evaluate False.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("empty timestamp")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _result(
    status: str,
    blockers: list[str],
    *,
    enabled: bool,
    epoch: BudgetEpoch | None,
    projected_turnover_usdt: float | None,
    remaining_cycles: int | None,
    remaining_turnover_usdt: float | None,
    age_seconds: float | None,
) -> dict[str, Any]:
    return {
        "contract_version": GATE_CONTRACT_VERSION,
        "status": status,
        "passed": status in {"passed", "disabled"},
        "enforcement": "enabled" if enabled else "disabled",
        "blockers": sorted(set(blockers)),
        "epoch_id": epoch.epoch_id if epoch is not None else None,
        "epoch_status": epoch.status if epoch is not None else None,
        "epoch_created_at_utc": epoch.created_at_utc if epoch is not None else None,
        "epoch_age_seconds": age_seconds,
        "max_live_cycles": _coerce_int(epoch.max_live_cycles) if epoch is not None else None,
        "consumed_cycles": _coerce_int(epoch.consumed_cycles) if epoch is not None else None,
        "remaining_cycles": remaining_cycles,
        "max_gross_turnover_usdt": _coerce_finite_float(epoch.max_gross_turnover_usdt) if epoch is not None else None,
        "consumed_turnover_usdt": _coerce_finite_float(epoch.consumed_turnover_usdt) if epoch is not None else None,
        "remaining_turnover_usdt": remaining_turnover_usdt,
        "max_age_seconds": _coerce_int(epoch.max_age_seconds) if epoch is not None else None,
        "projected_cycle_turnover_usdt": projected_turnover_usdt,
    }


def evaluate_unattended_budget_gate(
    epoch: BudgetEpoch | None,
    *,
    enabled: bool,
    projected_turnover_usdt: float | None,
    now_utc: datetime,
) -> dict[str, Any]:
    """Decide whether one more live-submitting cycle may run under the budget.

    Fail-closed on every ambiguity. Emits a blocker (and the existing cycle
    machinery cascades it to ``disarm_on_blocker``) when, with the gate enabled:

      - no open epoch exists                       -> unattended_budget_no_open_epoch
      - epoch status is not "open"                 -> unattended_budget_epoch_not_open
      - any bound is non-coercible / non-finite    -> unattended_budget_ledger_corrupt
      - any configured bound is non-positive       -> unattended_budget_*_not_positive
      - created_at is unparseable                  -> unattended_budget_epoch_created_at_unparseable
      - epoch older than max_age_seconds           -> unattended_budget_epoch_stale
      - consumed/turnover counters are negative    -> unattended_budget_ledger_corrupt
      - cycle budget already exhausted             -> unattended_budget_cycle_exhausted
      - projected turnover is None or non-finite   -> unattended_budget_projected_turnover_unknown
      - consumed + projected turnover > budget      -> unattended_budget_turnover_exhausted

    All blocker codes share the ``unattended_budget`` substring so a single
    health-monitor hard-fragment makes any budget disarm non-auto-recoverable.

    When ``enabled`` is False, returns a no-op "disabled" result with no blockers,
    so attended / canary / single-run flows are untouched.

    ``projected_turnover_usdt`` is THIS cycle's planned gross turnover (sum of
    |planned order notional| from the dry-run plan), checked BEFORE submit so an
    order that would breach the remaining turnover budget never reaches the
    exchange. Pass None (never 0.0 as a guess) when it cannot be computed; the
    gate then fails closed rather than silently permitting. A non-finite value is
    treated identically to None.
    """
    if not enabled:
        return _result(
            "disabled",
            [],
            enabled=False,
            epoch=epoch,
            projected_turnover_usdt=projected_turnover_usdt,
            remaining_cycles=None,
            remaining_turnover_usdt=None,
            age_seconds=None,
        )

    blockers: list[str] = []

    if epoch is None:
        blockers.append("unattended_budget_no_open_epoch")
        return _result(
            "blocked",
            blockers,
            enabled=True,
            epoch=None,
            projected_turnover_usdt=projected_turnover_usdt,
            remaining_cycles=None,
            remaining_turnover_usdt=None,
            age_seconds=None,
        )

    # Defensive numeric coercion FIRST: any non-coercible or non-finite field is
    # a fail-closed corruption, never a silently-skipped comparison.
    max_cycles = _coerce_int(epoch.max_live_cycles)
    consumed_cycles = _coerce_int(epoch.consumed_cycles)
    max_age = _coerce_int(epoch.max_age_seconds)
    max_turnover = _coerce_finite_float(epoch.max_gross_turnover_usdt)
    consumed_turnover = _coerce_finite_float(epoch.consumed_turnover_usdt)

    if str(epoch.status).strip().lower() != EPOCH_STATUS_OPEN:
        blockers.append(f"unattended_budget_epoch_not_open:{epoch.status}")
    if None in (max_cycles, consumed_cycles, max_age, max_turnover, consumed_turnover):
        blockers.append("unattended_budget_ledger_corrupt")
    if max_cycles is not None and max_cycles <= 0:
        blockers.append("unattended_budget_max_cycles_not_positive")
    if max_turnover is not None and max_turnover <= 0.0:
        blockers.append("unattended_budget_max_turnover_not_positive")
    if max_age is not None and max_age <= 0:
        blockers.append("unattended_budget_max_age_not_positive")
    if (consumed_cycles is not None and consumed_cycles < 0) or (
        consumed_turnover is not None and consumed_turnover < 0.0
    ):
        blockers.append("unattended_budget_ledger_corrupt")

    age_seconds: float | None = None
    try:
        created = _parse_utc(epoch.created_at_utc)
        age_seconds = max(0.0, (now_utc.astimezone(UTC) - created).total_seconds())
        if max_age is not None and max_age > 0 and age_seconds > float(max_age):
            blockers.append(f"unattended_budget_epoch_stale:{age_seconds:.0f}>{max_age}")
    except (ValueError, TypeError):
        blockers.append("unattended_budget_epoch_created_at_unparseable")

    remaining_cycles = (
        max_cycles - consumed_cycles
        if max_cycles is not None and consumed_cycles is not None
        else None
    )
    if max_cycles is not None and consumed_cycles is not None and consumed_cycles >= max_cycles:
        blockers.append(f"unattended_budget_cycle_exhausted:{consumed_cycles}>={max_cycles}")

    remaining_turnover = (
        max_turnover - consumed_turnover
        if max_turnover is not None and consumed_turnover is not None
        else None
    )
    projected = _coerce_finite_float(projected_turnover_usdt) if projected_turnover_usdt is not None else None
    if projected is None:
        blockers.append("unattended_budget_projected_turnover_unknown")
    else:
        projected = max(0.0, projected)
        if (
            max_turnover is not None
            and consumed_turnover is not None
            and consumed_turnover + projected > max_turnover + _TURNOVER_EPS
        ):
            blockers.append(
                "unattended_budget_turnover_exhausted:"
                f"{consumed_turnover + projected:.2f}>{max_turnover:.2f}"
            )

    status = "passed" if not blockers else "blocked"
    return _result(
        status,
        blockers,
        enabled=True,
        epoch=epoch,
        projected_turnover_usdt=projected,
        remaining_cycles=remaining_cycles,
        remaining_turnover_usdt=remaining_turnover,
        age_seconds=age_seconds,
    )


def epoch_status_after_consume(epoch: BudgetEpoch) -> str:
    """Status an epoch should take once its consumed totals are updated.

    Used by the persistence layer after an idempotent consume so an exhausted
    epoch is marked terminal (and the gate's not-open branch then fails closed
    even if a later read race re-reads it). Fails SAFE: any non-finite /
    unreadable total is treated as terminal so a poisoned epoch is never
    returned 'open'.
    """
    consumed_cycles = _coerce_int(epoch.consumed_cycles)
    max_cycles = _coerce_int(epoch.max_live_cycles)
    consumed_turnover = _coerce_finite_float(epoch.consumed_turnover_usdt)
    max_turnover = _coerce_finite_float(epoch.max_gross_turnover_usdt)
    if None in (consumed_cycles, max_cycles, consumed_turnover, max_turnover):
        return EPOCH_STATUS_EXHAUSTED
    if consumed_cycles >= max_cycles:
        return EPOCH_STATUS_EXHAUSTED
    if consumed_turnover >= max_turnover - _TURNOVER_EPS:
        return EPOCH_STATUS_EXHAUSTED
    return EPOCH_STATUS_OPEN
