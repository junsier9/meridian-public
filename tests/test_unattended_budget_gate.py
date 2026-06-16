from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.unattended_budget_gate import (  # noqa: E402
    EPOCH_STATUS_CLOSED,
    EPOCH_STATUS_EXHAUSTED,
    EPOCH_STATUS_OPEN,
    BudgetEpoch,
    epoch_status_after_consume,
    evaluate_unattended_budget_gate,
)


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)


def _epoch(**overrides):
    base = dict(
        epoch_id="epoch-1",
        created_at_utc=(NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        max_live_cycles=6,
        max_gross_turnover_usdt=600.0,
        max_age_seconds=3600,
        consumed_cycles=0,
        consumed_turnover_usdt=0.0,
        status=EPOCH_STATUS_OPEN,
    )
    base.update(overrides)
    return BudgetEpoch(**base)


def _has(result, fragment):
    return any(fragment in b for b in result["blockers"])


def test_disabled_is_noop_even_without_epoch():
    result = evaluate_unattended_budget_gate(
        None, enabled=False, projected_turnover_usdt=None, now_utc=NOW
    )
    assert result["status"] == "disabled"
    assert result["passed"] is True
    assert result["blockers"] == []
    assert result["enforcement"] == "disabled"


def test_enabled_no_epoch_fails_closed():
    result = evaluate_unattended_budget_gate(
        None, enabled=True, projected_turnover_usdt=100.0, now_utc=NOW
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_no_open_epoch")


def test_happy_path_within_budget_passes():
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=2, consumed_turnover_usdt=200.0),
        enabled=True,
        projected_turnover_usdt=107.0,
        now_utc=NOW,
    )
    assert result["passed"] is True, result["blockers"]
    assert result["remaining_cycles"] == 4
    assert result["remaining_turnover_usdt"] == 400.0


def test_cycle_budget_exhausted_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=6, max_live_cycles=6),
        enabled=True,
        projected_turnover_usdt=10.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_cycle_exhausted")


def test_turnover_budget_would_exceed_fails_closed():
    # consumed 550 + projected 100 = 650 > 600 ceiling
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=3, consumed_turnover_usdt=550.0),
        enabled=True,
        projected_turnover_usdt=100.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_turnover_exhausted")


def test_turnover_exact_boundary_passes():
    # consumed 525 + projected 75 = 600 == ceiling -> allowed (eps tolerance)
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=3, consumed_turnover_usdt=525.0),
        enabled=True,
        projected_turnover_usdt=75.0,
        now_utc=NOW,
    )
    assert result["passed"] is True, result["blockers"]


def test_single_projected_cycle_over_whole_budget_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=0, consumed_turnover_usdt=0.0, max_gross_turnover_usdt=150.0),
        enabled=True,
        projected_turnover_usdt=200.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_turnover_exhausted")


def test_stale_epoch_fails_closed_even_with_budget_left():
    old = (NOW - timedelta(seconds=4000)).isoformat().replace("+00:00", "Z")
    result = evaluate_unattended_budget_gate(
        _epoch(created_at_utc=old, max_age_seconds=3600, consumed_cycles=0),
        enabled=True,
        projected_turnover_usdt=10.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_epoch_stale")


def test_projected_turnover_unknown_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(),
        enabled=True,
        projected_turnover_usdt=None,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_projected_turnover_unknown")


def test_non_open_status_fails_closed():
    for status in (EPOCH_STATUS_EXHAUSTED, EPOCH_STATUS_CLOSED, "paused", ""):
        result = evaluate_unattended_budget_gate(
            _epoch(status=status),
            enabled=True,
            projected_turnover_usdt=10.0,
            now_utc=NOW,
        )
        assert result["passed"] is False, status
        assert _has(result, "unattended_budget_epoch_not_open")


def test_non_positive_bounds_fail_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(max_live_cycles=0, max_gross_turnover_usdt=0.0, max_age_seconds=0),
        enabled=True,
        projected_turnover_usdt=10.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_max_cycles_not_positive")
    assert _has(result, "unattended_budget_max_turnover_not_positive")
    assert _has(result, "unattended_budget_max_age_not_positive")


def test_negative_consumed_is_corrupt_fail_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=-1, consumed_turnover_usdt=-5.0),
        enabled=True,
        projected_turnover_usdt=10.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_ledger_corrupt")


def test_unparseable_created_at_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(created_at_utc="not-a-timestamp"),
        enabled=True,
        projected_turnover_usdt=10.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_epoch_created_at_unparseable")


def test_last_cycle_with_fitting_turnover_passes_then_next_is_exhausted():
    # 5 of 6 cycles consumed, last cycle fits -> passes
    ok = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=5, consumed_turnover_usdt=400.0),
        enabled=True,
        projected_turnover_usdt=100.0,
        now_utc=NOW,
    )
    assert ok["passed"] is True, ok["blockers"]
    assert ok["remaining_cycles"] == 1
    # after that 6th cycle is consumed, the next evaluation is exhausted
    exhausted = evaluate_unattended_budget_gate(
        _epoch(consumed_cycles=6, consumed_turnover_usdt=500.0),
        enabled=True,
        projected_turnover_usdt=1.0,
        now_utc=NOW,
    )
    assert exhausted["passed"] is False
    assert _has(exhausted, "unattended_budget_cycle_exhausted")


def test_nan_consumed_turnover_fails_closed():
    # IEEE-754: nan < 0, nan + x > cap, etc. are all False. Without the finite
    # guard this slipped past every check and returned passed=True.
    result = evaluate_unattended_budget_gate(
        _epoch(consumed_turnover_usdt=float("nan")),
        enabled=True,
        projected_turnover_usdt=100.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_ledger_corrupt")


def test_inf_max_turnover_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(max_gross_turnover_usdt=float("inf")),
        enabled=True,
        projected_turnover_usdt=100.0,
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_ledger_corrupt")


def test_nan_projected_turnover_fails_closed_not_clamped_to_zero():
    # max(0.0, nan) == 0.0 would have scored a NaN projected as a free cycle.
    result = evaluate_unattended_budget_gate(
        _epoch(),
        enabled=True,
        projected_turnover_usdt=float("nan"),
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_projected_turnover_unknown")
    assert result["projected_cycle_turnover_usdt"] != 0.0


def test_inf_projected_turnover_fails_closed():
    result = evaluate_unattended_budget_gate(
        _epoch(),
        enabled=True,
        projected_turnover_usdt=float("inf"),
        now_utc=NOW,
    )
    assert result["passed"] is False
    assert _has(result, "unattended_budget_projected_turnover_unknown")


def test_non_finite_consumed_makes_epoch_terminal():
    # A poisoned epoch must never be returned 'open'.
    assert (
        epoch_status_after_consume(_epoch(consumed_turnover_usdt=float("nan")))
        == EPOCH_STATUS_EXHAUSTED
    )
    assert (
        epoch_status_after_consume(_epoch(max_gross_turnover_usdt=float("inf")))
        == EPOCH_STATUS_EXHAUSTED
    )


def test_epoch_status_after_consume_marks_exhausted():
    assert (
        epoch_status_after_consume(_epoch(consumed_cycles=6, max_live_cycles=6))
        == EPOCH_STATUS_EXHAUSTED
    )
    assert (
        epoch_status_after_consume(
            _epoch(consumed_turnover_usdt=600.0, max_gross_turnover_usdt=600.0)
        )
        == EPOCH_STATUS_EXHAUSTED
    )
    assert (
        epoch_status_after_consume(_epoch(consumed_cycles=2, consumed_turnover_usdt=200.0))
        == EPOCH_STATUS_OPEN
    )
